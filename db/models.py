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
        Index('idx_email_auth_method', 'email', 'auth_method'),
        Index('idx_created_at', 'created_at'),
        Index('idx_last_login', 'last_login'),
        Index('idx_active_users', 'is_active', 'auth_method'),  # New: For active user queries
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
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