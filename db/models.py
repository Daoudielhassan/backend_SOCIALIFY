from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    password_hash = Column(String(256), nullable=True)  # Will be deprecated for OAuth-only
    google_id = Column(String(128), nullable=True)
    gmail_token_encrypted = Column(Text, nullable=True)  # Encrypted OAuth token storage
    whatsapp_number = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow, nullable=True)
    auth_method = Column(String(50), default='oauth', nullable=False)  # Default to OAuth
    
    # Relationships
    messages = relationship("MessageMetadata", back_populates="user")
    
    # Optimized indexes for common query patterns
    __table_args__ = (
        Index('idx_user_email_auth_method', 'email', 'auth_method'),
        Index('idx_user_created_at', 'created_at'),
        Index('idx_user_last_login', 'last_login'),
        Index('idx_user_active_users', 'is_active', 'auth_method'),  # New: For active user queries
        Index('idx_gmail_token_encrypted', 'gmail_token_encrypted'),  # New: For token lookups
    )
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'auth_method': self.auth_method,
            'created_at': self.created_at.isoformat() if self.created_at is not None else None,
            'last_login': self.last_login.isoformat() if self.last_login is not None else None
        }

class MessageMetadata(Base):
    """
    Privacy-focused message storage - NO CONTENT STORED
    Only metadata and AI analysis results are kept
    """
    __tablename__ = "message_metadata"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source = Column(String(32), nullable=False)  # 'gmail' or 'whatsapp'
    external_id = Column(String(128), nullable=True)  # External service message ID
    sender_domain = Column(String(120), nullable=True)  # Only domain, not full email
    subject_preview = Column(String(100), nullable=True)  # Truncated subject for privacy
    received_at = Column(DateTime, nullable=False)
    
    # AI Analysis Results (no original content)
    predicted_priority = Column(String(32), nullable=True)
    predicted_context = Column(String(128), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    
    # User feedback for AI improvement
    feedback_priority = Column(String(32), nullable=True)
    feedback_context = Column(String(128), nullable=True)
    used_in_retrain = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="messages")
    
    # Optimized indexes for high-performance queries
    __table_args__ = (
        # Unique constraint to prevent duplicate messages
        Index('uq_user_received_subject', 'user_id', 'received_at', 'subject_preview', unique=True),
        
        # Core indexes for common queries
        Index('idx_user_source', 'user_id', 'source'),
        Index('idx_external_id', 'external_id'),
        Index('idx_received_at', 'received_at'),
        Index('idx_priority', 'predicted_priority'),
        
        # Composite indexes for complex query patterns
        Index('idx_user_received_priority', 'user_id', 'received_at', 'predicted_priority'),  # Dashboard queries
        Index('idx_user_source_received', 'user_id', 'source', 'received_at'),  # Source-specific timelines
        Index('idx_sender_domain_user', 'sender_domain', 'user_id'),  # Sender analytics
        Index('idx_context_priority', 'predicted_context', 'predicted_priority'),  # Analytics queries
        Index('idx_feedback_analysis', 'user_id', 'feedback_priority', 'feedback_context'),  # ML training
        Index('idx_processed_at', 'processed_at'),  # Processing status queries
        
        # Privacy and compliance indexes
        Index('idx_user_privacy_check', 'user_id', 'created_at', 'processed_at'),  # Privacy audits
    )
    
    def __repr__(self):
        return f'<MessageMetadata {self.id} from {self.sender_domain}>'

# DEPRECATED MESSAGE MODEL REMOVED
# The old Message model with content storage has been removed for privacy compliance.
# All message operations now use MessageMetadata (privacy-focused, metadata-only).
# 
# Migration completed: Content storage eliminated, privacy-first architecture implemented.
# For any legacy integrations, update to use MessageMetadata instead.

class WhatsAppMessage(Base):
    """
    WhatsApp message tracking - Metadata only for privacy compliance
    """
    __tablename__ = "whatsapp_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(String(256), nullable=False, unique=True)  # WhatsApp message ID
    recipient_number = Column(String(32), nullable=False)  # Phone number (encrypted in production)
    message_type = Column(String(50), default="text")  # text, template, etc.
    template_name = Column(String(100), nullable=True)  # Template name if applicable
    status = Column(String(50), default="sent")  # sent, delivered, read, failed
    error_message = Column(Text, nullable=True)  # Error details if failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="whatsapp_messages")
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_user_whatsapp', 'user_id', 'created_at'),
        Index('idx_whatsapp_message_id', 'message_id'),
        Index('idx_recipient', 'recipient_number'),
        Index('idx_status', 'status', 'created_at'),
        Index('idx_message_type', 'message_type'),
    )
    
    def __repr__(self):
        return f'<WhatsAppMessage {self.message_id} to {self.recipient_number[:5]}***>'

class WhatsAppWebhook(Base):
    """
    WhatsApp webhook events tracking
    """
    __tablename__ = "whatsapp_webhooks"
    
    id = Column(Integer, primary_key=True, index=True)
    webhook_id = Column(String(256), nullable=False)  # Unique webhook event ID
    event_type = Column(String(50), nullable=False)  # message, status, etc.
    from_number = Column(String(32), nullable=True)  # Sender phone number
    message_id = Column(String(256), nullable=True)  # Related message ID
    status = Column(String(50), nullable=True)  # Message status update
    webhook_data = Column(JSON, nullable=True)  # Raw webhook data (filtered for privacy)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_webhook_id', 'webhook_id'),
        Index('idx_event_type', 'event_type', 'created_at'),
        Index('idx_processed', 'processed', 'created_at'),
        Index('idx_from_number', 'from_number'),
        Index('idx_message_tracking', 'message_id', 'status'),
    )
    
    def __repr__(self):
        return f'<WhatsAppWebhook {self.webhook_id} - {self.event_type}>'

class WhatsAppBusinessAccount(Base):
    """
    Multi-tenant WhatsApp Business Account configuration
    Each user can connect their own WABA
    """
    __tablename__ = "whatsapp_business_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    waba_id = Column(String(128), nullable=False, unique=True)  # WhatsApp Business Account ID
    business_name = Column(String(256), nullable=True)
    
    # Encrypted credentials
    access_token_encrypted = Column(Text, nullable=False)  # Long-lived access token (encrypted)
    refresh_token_encrypted = Column(Text, nullable=True)  # Refresh token (encrypted)
    
    # Meta OAuth details
    meta_app_id = Column(String(128), nullable=True)
    meta_user_id = Column(String(128), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    webhook_configured = Column(Boolean, default=False)
    
    # Timestamps
    connected_at = Column(DateTime, default=datetime.utcnow)
    last_sync = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="whatsapp_accounts")
    phone_numbers = relationship("WhatsAppPhoneNumber", back_populates="business_account")
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_user_waba', 'user_id', 'waba_id'),
        Index('idx_waba_active', 'waba_id', 'is_active'),
        Index('idx_token_expires', 'token_expires_at'),
        Index('idx_last_sync', 'last_sync'),
    )
    
    def __repr__(self):
        return f'<WhatsAppBusinessAccount {self.waba_id} - {self.business_name}>'

class WhatsAppPhoneNumber(Base):
    """
    Phone numbers associated with WhatsApp Business Accounts
    """
    __tablename__ = "whatsapp_phone_numbers"
    
    id = Column(Integer, primary_key=True, index=True)
    waba_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=False)
    phone_number_id = Column(String(128), nullable=False, unique=True)  # Meta phone number ID
    phone_number = Column(String(32), nullable=False)  # Actual phone number
    display_name = Column(String(256), nullable=True)
    
    # Status and verification
    status = Column(String(50), default="pending")  # pending, verified, rejected
    is_verified = Column(Boolean, default=False)
    webhook_configured = Column(Boolean, default=False)
    
    # Configuration
    webhook_url = Column(String(512), nullable=True)
    webhook_verify_token = Column(String(256), nullable=True)
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)
    
    # Relationships
    business_account = relationship("WhatsAppBusinessAccount", back_populates="phone_numbers")
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_phone_number_id', 'phone_number_id'),
        Index('idx_waba_phone', 'waba_id', 'phone_number_id'),
        Index('idx_phone_status', 'phone_number', 'status'),
        Index('idx_webhook_configured', 'webhook_configured'),
    )
    
    def __repr__(self):
        return f'<WhatsAppPhoneNumber {self.phone_number} ({self.phone_number_id})>'

class WhatsAppMessageV2(Base):
    """
    Multi-tenant WhatsApp messages with tenant routing
    """
    __tablename__ = "whatsapp_messages_v2"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    waba_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=False)
    phone_number_id = Column(Integer, ForeignKey("whatsapp_phone_numbers.id"), nullable=False)
    
    # Message details
    message_id = Column(String(256), nullable=False, unique=True)  # WhatsApp message ID
    direction = Column(String(20), nullable=False)  # 'inbound', 'outbound'
    
    # Contact information
    contact_phone = Column(String(32), nullable=False)  # Customer's phone number
    contact_name = Column(String(256), nullable=True)  # Customer's name
    
    # Message content (privacy-aware)
    message_type = Column(String(50), default="text")  # text, template, image, etc.
    template_name = Column(String(100), nullable=True)  # Template name if applicable
    content_hash = Column(String(128), nullable=True)  # Hash of content for deduplication
    
    # Status tracking
    status = Column(String(50), default="sent")  # sent, delivered, read, failed
    error_message = Column(Text, nullable=True)  # Error details if failed
    
    # AI Processing
    ai_processed = Column(Boolean, default=False)
    predicted_priority = Column(String(50), nullable=True)
    predicted_context = Column(String(100), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    
    # Timestamps
    sent_at = Column(DateTime, nullable=True)  # When message was sent
    delivered_at = Column(DateTime, nullable=True)  # When message was delivered
    read_at = Column(DateTime, nullable=True)  # When message was read
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    business_account = relationship("WhatsAppBusinessAccount")
    phone_number = relationship("WhatsAppPhoneNumber")
    
    # Optimized indexes
    __table_args__ = (
        Index('idx_user_messages', 'user_id', 'created_at'),
        Index('idx_waba_messages', 'waba_id', 'created_at'),
        Index('idx_phone_messages', 'phone_number_id', 'created_at'),
        Index('idx_metadata_message_id', 'message_id'),
        Index('idx_contact_phone', 'contact_phone', 'created_at'),
        Index('idx_direction_status', 'direction', 'status'),
        Index('idx_ai_processing', 'ai_processed', 'created_at'),
        Index('idx_metadata_status_tracking', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f'<WhatsAppMessageV2 {self.message_id} - {self.direction}>' 