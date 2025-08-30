"""
Enhanced Multi-Tenant WhatsApp SaaS Database Models
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, Index, JSON, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from db.db import Base

class User(Base):
    """
    Enhanced User model for multi-tenant SaaS
    Each user is a tenant with their own WhatsApp Business Account
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    
    # OAuth Authentication
    google_id = Column(String(128), nullable=True)
    gmail_token_encrypted = Column(Text, nullable=True)
    
    # Meta OAuth for WhatsApp Business
    meta_user_id = Column(String(128), nullable=True, index=True)
    meta_access_token_encrypted = Column(Text, nullable=True)  # Long-lived token
    meta_token_expires_at = Column(DateTime, nullable=True)
    meta_permissions = Column(JSON, nullable=True)  # Granted permissions
    
    # Account status
    is_active = Column(Boolean, default=True)
    subscription_tier = Column(String(50), default='free')  # free, pro, enterprise
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
    """
    WhatsApp Business Account (WABA) for each tenant
    Each user can have multiple WABAs
    """
    __tablename__ = "whatsapp_business_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Meta WhatsApp Business Account Details
    waba_id = Column(String(128), nullable=False, unique=True, index=True)
    waba_name = Column(String(256), nullable=True)
    phone_number_id = Column(String(128), nullable=False, unique=True, index=True)
    phone_number = Column(String(32), nullable=False, index=True)  # +1234567890
    display_phone_number = Column(String(32), nullable=True)
    
    # Account Status
    is_active = Column(Boolean, default=True)
    status = Column(String(50), default='pending')  # pending, active, suspended, error
    webhook_configured = Column(Boolean, default=False)
    
    # Rate Limiting & Messaging Tier
    messaging_tier = Column(String(50), default='standard')  # standard, enhanced
    rate_limit_tier = Column(String(50), default='standard')
    daily_message_limit = Column(Integer, default=1000)
    current_daily_count = Column(Integer, default=0)
    last_reset_date = Column(DateTime, default=datetime.utcnow)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="whatsapp_accounts")
    messages = relationship("WhatsAppMessage", back_populates="business_account", cascade="all, delete-orphan")
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_user_waba', 'user_id', 'waba_id'),
        Index('idx_phone_number_id', 'phone_number_id'),
        Index('idx_phone_number', 'phone_number'),
        Index('idx_active_accounts', 'is_active', 'status'),
        Index('idx_daily_limits', 'current_daily_count', 'last_reset_date'),
    )
    
    def __repr__(self):
        return f'<WABA {self.waba_id} - {self.phone_number}>'

class WhatsAppMessage(Base):
    """
    Enhanced WhatsApp message tracking with tenant isolation
    """
    __tablename__ = "whatsapp_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Tenant isolation
    business_account_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=False)
    
    # Message Identifiers
    message_id = Column(String(256), nullable=False, unique=True, index=True)  # WhatsApp message ID
    conversation_id = Column(String(256), nullable=True, index=True)  # Group conversations
    
    # Message Details
    direction = Column(String(20), nullable=False)  # 'inbound', 'outbound'
    from_number = Column(String(32), nullable=True)  # For inbound messages
    to_number = Column(String(32), nullable=True)    # For outbound messages
    message_type = Column(String(50), default="text")  # text, template, media, etc.
    template_name = Column(String(100), nullable=True)
    
    # Status & Delivery
    status = Column(String(50), default="sent")  # sent, delivered, read, failed
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Pricing & Analytics
    pricing_category = Column(String(50), nullable=True)  # utility, authentication, marketing
    pricing_model = Column(String(50), nullable=True)     # conversation, template
    cost_usd = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="whatsapp_messages")
    business_account = relationship("WhatsAppBusinessAccount", back_populates="messages")
    
    # Optimized indexes for multi-tenant queries
    __table_args__ = (
        Index('idx_tenant_messages', 'user_id', 'business_account_id', 'created_at'),
        Index('idx_conversation', 'conversation_id', 'created_at'),
        Index('idx_phone_numbers', 'from_number', 'to_number'),
        Index('idx_v2_status_tracking', 'status', 'direction', 'created_at'),
        Index('idx_pricing', 'pricing_category', 'cost_usd'),
        Index('idx_v2_message_id', 'message_id'),
    )
    
    def __repr__(self):
        return f'<WAMessage {self.message_id} - {self.direction}>'

class WhatsAppWebhookEvent(Base):
    """
    Enhanced webhook event tracking with tenant routing
    """
    __tablename__ = "whatsapp_webhook_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Resolved tenant
    business_account_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=True)
    
    # Webhook Details
    webhook_id = Column(String(256), nullable=False, unique=True, index=True)
    event_type = Column(String(50), nullable=False)  # message, status, account_review
    phone_number_id = Column(String(128), nullable=True, index=True)  # For routing
    
    # Processing Status
    processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Raw Data (filtered for privacy)
    webhook_data = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_webhook_routing', 'phone_number_id', 'event_type'),
        Index('idx_processing_queue', 'processed', 'retry_count', 'created_at'),
        Index('idx_tenant_webhooks', 'user_id', 'business_account_id'),
        Index('idx_webhook_id', 'webhook_id'),
    )
    
    def __repr__(self):
        return f'<WebhookEvent {self.webhook_id} - {self.event_type}>'

class MessageMetadata(Base):
    """
    Enhanced privacy-focused message metadata with tenant isolation
    """
    __tablename__ = "message_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Tenant isolation
    business_account_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=True)
    
    # Source & Identification
    source = Column(String(32), nullable=False)  # 'gmail', 'whatsapp'
    external_id = Column(String(256), nullable=True, index=True)  # WhatsApp message ID
    
    # Privacy-compliant content preview
    subject_preview = Column(String(100), nullable=True)  # First 100 chars
    content_hash = Column(String(64), nullable=True)      # SHA-256 hash for deduplication
    
    # AI Predictions
    predicted_priority = Column(String(50), nullable=True)  # high, medium, low
    predicted_context = Column(String(100), nullable=True)  # work, personal, urgent, etc.
    prediction_confidence = Column(Float, nullable=True)
    prediction_details = Column(JSON, nullable=True)
    
    # User Feedback for ML Training
    feedback_priority = Column(String(50), nullable=True)
    feedback_context = Column(String(100), nullable=True)
    feedback_provided_at = Column(DateTime, nullable=True)
    
    # Processing Status
    ai_processed = Column(Boolean, default=False)
    
    # Timestamps
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="messages")
    
    # Optimized indexes for multi-tenant analytics
    __table_args__ = (
        Index('idx_tenant_metadata', 'user_id', 'source', 'created_at'),
        Index('idx_ai_processing', 'ai_processed', 'created_at'),
        Index('idx_predictions', 'predicted_priority', 'predicted_context'),
        Index('idx_feedback', 'feedback_priority', 'feedback_context'),
        Index('idx_external_id', 'external_id'),
        Index('idx_content_hash', 'content_hash'),  # For deduplication
    )
    
    def __repr__(self):
        return f'<MessageMetadata {self.id} - {self.source}>'

class TenantConfiguration(Base):
    """
    Per-tenant configuration and feature flags
    """
    __tablename__ = "tenant_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Feature Flags
    whatsapp_enabled = Column(Boolean, default=True)
    gmail_enabled = Column(Boolean, default=True)
    ai_processing_enabled = Column(Boolean, default=True)
    webhook_notifications_enabled = Column(Boolean, default=True)
    
    # WhatsApp Specific Settings
    auto_reply_enabled = Column(Boolean, default=False)
    auto_reply_message = Column(Text, nullable=True)
    business_hours_enabled = Column(Boolean, default=False)
    business_hours_config = Column(JSON, nullable=True)  # Timezone, hours, days
    
    # Rate Limiting & Quotas
    daily_message_quota = Column(Integer, default=1000)
    monthly_message_quota = Column(Integer, default=30000)
    current_month_count = Column(Integer, default=0)
    quota_reset_date = Column(DateTime, default=datetime.utcnow)
    
    # Webhook Settings
    webhook_url = Column(String(512), nullable=True)  # Custom webhook endpoint
    webhook_secret = Column(String(256), nullable=True)
    webhook_events = Column(JSON, nullable=True)  # Which events to forward
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="configuration")
    
    # Indexes
    __table_args__ = (
        Index('idx_user_config', 'user_id'),
        Index('idx_quotas', 'daily_message_quota', 'current_month_count'),
    )
    
    def __repr__(self):
        return f'<TenantConfig {self.user_id}>'
