"""
High-Performance Email Service - Optimized Operations
Enhanced email service with caching, batching, and async optimizations
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.performance import (
    performance_cache, cached, batch_processor, query_optimizer,
    monitor_performance
)
from utils.logger import logger
from config.settings import settings
from services.emailServices.gmail_oauth import GmailOAuthService
from db.models import User, MessageMetadata

class HighPerformanceEmailService:
    """
    Enhanced email service with performance optimizations
    
    Extends the base EmailService with:
    - Intelligent caching for Gmail API responses
    - Batch processing for multiple users
    - Parallel API calls for improved throughput
    - Optimized database operations
    """
    
    def __init__(self):
        """Initialize the high-performance email service"""
        self.auth_service = GmailOAuthService()
        self.cache_ttl = {
            'messages': 300,  # 5 minutes
            'user_stats': 600,  # 10 minutes
            'labels': 1800,   # 30 minutes
        }
    
    async def fetch_messages_for_user(
        self,
        user: User,
        db: AsyncSession,
        provider: str = "gmail",
        max_results: int = 100,
        privacy_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Base method to fetch messages for a user from Gmail API
        """
        # Extract values from User model to avoid SQLAlchemy column type issues
        user_id = getattr(user, 'id', 0)
        gmail_token = getattr(user, 'gmail_token_encrypted', None)
        
        # Verify database session is async-capable
        if not hasattr(db, 'commit'):
            logger.error(f"Database session for user {user_id} is not properly configured")
            return {"error": "Database configuration error", "processed": 0}
        
        try:
            # Get Gmail service for user
            if not gmail_token:
                logger.error(f"User {user_id} has no Gmail token")
                return {"error": "Gmail account not connected", "processed": 0}
                
            service, updated_credentials = self.auth_service.get_gmail_service(gmail_token)
            if not service:
                logger.error(f"Failed to get Gmail service for user {user_id}")
                return {"error": "Gmail authentication failed", "processed": 0}
            
            # Fetch messages from Gmail API
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            processed_count = 0
            
            for message in messages:
                try:
                    # Get message details
                    msg = service.users().messages().get(userId='me', id=message['id']).execute()
                    
                    # Process message metadata with AI predictions
                    metadata = await self._extract_message_metadata_with_ai(msg, user_id, privacy_mode)
                    
                    # Store metadata with AI predictions in database
                    try:
                        stored = await self._store_message_metadata(user_id, metadata, db)
                        if stored:  # Only count if successfully stored (not duplicate)
                            processed_count += 1
                            logger.debug(f"Successfully processed message {message.get('id')} for user {user_id}")
                    except Exception as db_error:
                        logger.error(f"Database error for message {message.get('id')}: {str(db_error)}")
                        # Continue processing other messages even if one fails
                        continue
                        
                except Exception as msg_error:
                    logger.error(f"Error processing message {message.get('id')}: {str(msg_error)}")
                    continue
            
            logger.info(f"Processed {processed_count} messages for user {user_id}")
            return {"processed": processed_count, "total": len(messages)}
            
        except Exception as e:
            logger.error(f"Error fetching messages for user {user_id}: {e}")
            return {"error": str(e), "processed": 0}
    
    async def _extract_message_metadata_with_ai(self, message: Dict[str, Any], user_id: int, privacy_mode: bool = True) -> Dict[str, Any]:
        """Extract privacy-safe metadata from Gmail message with AI predictions"""
        payload = message.get('payload', {})
        headers = payload.get('headers', [])
        
        # Extract headers safely
        header_dict = {h['name']: h['value'] for h in headers}
        
        # Extract relevant metadata matching MessageMetadata model
        metadata = {
            'external_id': message.get('id'),
            'received_at': datetime.fromtimestamp(int(message.get('internalDate', 0)) / 1000),
            'subject_preview': header_dict.get('Subject', '')[:100] if header_dict.get('Subject') else None,
            'sender_domain': header_dict.get('From', '').split('@')[-1] if '@' in header_dict.get('From', '') else None,
        }
        
        # Add AI predictions
        try:
            from services.analytics.analytics_service import analytics_service
            
            if metadata.get('subject_preview') and metadata.get('sender_domain'):
                prediction = await analytics_service.predict_message_classification(
                    subject=metadata['subject_preview'],
                    sender_domain=metadata['sender_domain'],
                    source='gmail',
                    user_id=user_id
                )
                
                # Add AI predictions to metadata
                metadata.update({
                    'predicted_priority': prediction.get('priority'),
                    'predicted_context': prediction.get('context'),
                    'prediction_confidence': prediction.get('confidence', {}).get('priority', 0.5)
                })
                
                logger.debug(f"AI prediction added: {prediction.get('priority')} priority for '{metadata['subject_preview'][:30]}...'")
            
        except Exception as e:
            logger.warning(f"AI prediction failed for message {metadata.get('external_id')}: {str(e)}")
            # Continue without predictions
        
        return metadata
    
    def _extract_message_metadata(self, message: Dict[str, Any], privacy_mode: bool = True) -> Dict[str, Any]:
        """Extract privacy-safe metadata from Gmail message (legacy method)"""
        payload = message.get('payload', {})
        headers = payload.get('headers', [])
        
        # Extract headers safely
        header_dict = {h['name']: h['value'] for h in headers}
        
        # Extract relevant metadata matching MessageMetadata model
        metadata = {
            'external_id': message.get('id'),
            'received_at': datetime.fromtimestamp(int(message.get('internalDate', 0)) / 1000),
            'subject_preview': header_dict.get('Subject', '')[:100] if header_dict.get('Subject') else None,
            'sender_domain': header_dict.get('From', '').split('@')[-1] if '@' in header_dict.get('From', '') else None,
        }
        
        return metadata
    
    async def _store_message_metadata(self, user_id: int, metadata: Dict[str, Any], db: AsyncSession) -> bool:
        """Store message metadata in database. Returns True if stored, False if duplicate."""
        try:
            # Check for existing message first to avoid unique constraint violation
            from sqlalchemy import select
            
            existing_query = select(MessageMetadata).where(
                MessageMetadata.user_id == user_id,
                MessageMetadata.received_at == metadata.get('received_at'),
                MessageMetadata.subject_preview == metadata.get('subject_preview')
            )
            
            result = await db.execute(existing_query)
            existing_message = result.scalar_one_or_none()
            
            if existing_message:
                logger.debug(f"Duplicate message already exists: {metadata.get('subject_preview', 'Unknown')} from {metadata.get('sender_domain', 'Unknown')}")
                return False  # Message already exists
            
            # Create and insert new message metadata
            message_metadata = MessageMetadata(
                user_id=user_id,
                source='gmail',
                external_id=metadata['external_id'],
                sender_domain=metadata.get('sender_domain'),
                subject_preview=metadata.get('subject_preview'),
                received_at=metadata.get('received_at'),
                # Add AI predictions
                predicted_priority=metadata.get('predicted_priority'),
                predicted_context=metadata.get('predicted_context'),
                prediction_confidence=metadata.get('prediction_confidence')
            )
            
            db.add(message_metadata)
            await db.commit()
            logger.debug(f"Successfully stored message metadata for user {user_id}")
            return True
            
        except Exception as e:
            # Fallback: Check if it's a unique constraint violation
            error_msg = str(e).lower()
            if "unique" in error_msg or "duplicate" in error_msg or "integrity" in error_msg:
                logger.debug(f"Unique constraint violation caught: {metadata.get('subject_preview', 'Unknown')}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                return False  # Treat as duplicate
            else:
                logger.error(f"Error storing message metadata: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                return False  # Return False instead of raising to prevent cascading errors
    
    
    @cached(ttl=300, key_prefix="gmail_messages")
    @monitor_performance("fetch_gmail_messages_cached")
    async def fetch_messages_for_user_cached(
        self,
        user,
        db: AsyncSession,
        max_results: int = 100,
        query: str = "",
        privacy_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Cached version of message fetching with performance optimizations
        """
        try:
            # Check cache first using user ID and query parameters as key
            cache_key = performance_cache.cache_key(
                "gmail_messages",
                user.id,
                max_results,
                query,
                privacy_mode
            )
            
            # If not in cache, fetch from Gmail API
            result = await self.fetch_messages_for_user(
                user=user,
                db=db,
                provider="gmail",
                max_results=max_results,
                privacy_mode=privacy_mode
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Cached message fetch failed for user {user.id}: {e}")
            return {"error": str(e), "processed": 0}
    
    @monitor_performance("batch_message_processing")
    async def process_messages_batch(
        self,
        messages_data: List[Dict[str, Any]],
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Process multiple messages in batches for optimal performance
        """
        if not messages_data:
            return {"processed": 0, "errors": 0}
        
        try:
            from db.models import MessageMetadata
            
            # Prepare records for batch insert
            metadata_records = []
            
            for message_data in messages_data:
                metadata_record = {
                    'user_id': user_id,
                    'source': 'gmail',
                    'external_id': message_data.get('id'),
                    'sender_domain': self._extract_domain(message_data.get('sender', '')),
                    'subject_preview': message_data.get('subject', '')[:100] if message_data.get('subject') else None,
                    'received_at': message_data.get('received_at', datetime.utcnow()),
                    'predicted_priority': message_data.get('predicted_priority'),
                    'predicted_context': message_data.get('predicted_context'),
                    'prediction_confidence': message_data.get('prediction_confidence'),
                    'created_at': datetime.utcnow(),
                    'processed_at': datetime.utcnow()
                }
                metadata_records.append(metadata_record)
            
            # Batch insert with optimal performance
            inserted_count = await batch_processor.batch_database_inserts(
                db=db,
                model_class=MessageMetadata,
                records=metadata_records,
                batch_size=50  # Optimal batch size for message metadata
            )
            
            # Invalidate relevant caches
            await self._invalidate_user_caches(user_id)
            
            logger.info(f"Batch processed {inserted_count} messages for user {user_id}")
            
            return {
                "processed": inserted_count,
                "errors": len(messages_data) - inserted_count
            }
            
        except Exception as e:
            logger.error(f"Batch message processing failed: {e}")
            return {"processed": 0, "errors": len(messages_data), "error": str(e)}
    
    @monitor_performance("parallel_user_fetch")
    async def fetch_messages_for_multiple_users(
        self,
        user_sessions: List[tuple],  # List of (user, db_session) tuples
        max_results: int = 50
    ) -> Dict[int, Dict[str, Any]]:
        """
        Fetch messages for multiple users in parallel
        
        Args:
            user_sessions: List of (user, db_session) tuples
            max_results: Max messages per user
            
        Returns:
            Dictionary mapping user_id to fetch results
        """
        if not user_sessions:
            return {}
        
        # Create API calls for parallel execution
        api_calls = []
        user_ids = []
        
        for user, db in user_sessions:
            if user.gmail_token_encrypted:
                async def fetch_for_user(u=user, session=db):
                    return await self.fetch_messages_for_user_cached(
                        user=u,
                        db=session,
                        max_results=max_results
                    )
                
                api_calls.append(fetch_for_user)
                user_ids.append(user.id)
        
        # Execute in parallel with concurrency control
        results = await batch_processor.parallel_api_calls(
            api_calls=api_calls,
            max_concurrent=3,  # Conservative limit for Gmail API
            timeout=30.0
        )
        
        # Map results to user IDs
        user_results = {}
        for i, result in enumerate(results):
            if i < len(user_ids):
                user_results[user_ids[i]] = result if result else {"error": "Fetch failed", "processed": 0}
        
        return user_results
    
    @cached(ttl=600, key_prefix="user_email_stats")
    async def get_user_email_statistics(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get cached user email statistics with optimized queries
        """
        try:
            # Use optimized query for message statistics
            messages = await query_optimizer.get_user_messages_optimized(
                db=db,
                user_id=user_id,
                limit=1000,  # Reasonable limit for stats calculation
                days=days
            )
            
            # Calculate statistics
            stats = {
                "total_messages": len(messages),
                "sources": {},
                "priorities": {},
                "recent_activity": {},
                "top_senders": {}
            }
            
            # Process messages for statistics
            sender_counts = {}
            daily_counts = {}
            
            for message in messages:
                # Source stats
                source = message.source
                stats["sources"][source] = stats["sources"].get(source, 0) + 1
                
                # Priority stats
                priority = message.predicted_priority or "unknown"
                stats["priorities"][priority] = stats["priorities"].get(priority, 0) + 1
                
                # Sender stats (domain only for privacy)
                if message.sender_domain:
                    sender_counts[message.sender_domain] = sender_counts.get(message.sender_domain, 0) + 1
                
                # Daily activity
                if message.received_at:
                    day_key = message.received_at.strftime("%Y-%m-%d")
                    daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
            
            # Top senders (limited for privacy)
            stats["top_senders"] = dict(
                sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            
            # Recent activity (last 7 days)
            stats["recent_activity"] = dict(
                sorted(daily_counts.items(), reverse=True)[:7]
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get user email statistics: {e}")
            return {"error": str(e), "total_messages": 0}
    
    @monitor_performance("bulk_analytics_update")
    async def update_user_analytics_bulk(
        self,
        user_ids: List[int],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Update analytics for multiple users efficiently
        """
        try:
            # Get analytics data for all users in a single optimized query
            analytics_data = await query_optimizer.get_analytics_data_batch(
                db=db,
                user_ids=user_ids,
                days=30
            )
            
            # Process analytics updates
            updates = []
            for user_id, data in analytics_data.items():
                # Prepare analytics summary for caching
                summary = {
                    "user_id": user_id,
                    "message_count": sum(data["sources"].values()),
                    "source_breakdown": data["sources"],
                    "priority_breakdown": data["priorities"],
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                # Cache the analytics data
                cache_key = performance_cache.cache_key("user_analytics", user_id)
                await performance_cache.set(cache_key, summary, ttl=600)
            
            logger.info(f"Bulk updated analytics for {len(user_ids)} users")
            
            return {
                "updated_users": len(user_ids),
                "analytics_cached": len(analytics_data)
            }
            
        except Exception as e:
            logger.error(f"Bulk analytics update failed: {e}")
            return {"error": str(e), "updated_users": 0}
    
    async def _invalidate_user_caches(self, user_id: int):
        """Invalidate all cache entries for a user"""
        patterns = [
            f"gmail_messages:*:{user_id}:*",
            f"user_email_stats:*:{user_id}:*",
            f"user_analytics:{user_id}",
            f"func:*:{user_id}:*"
        ]
        
        for pattern in patterns:
            await performance_cache.invalidate_pattern(pattern)
    
    def _extract_domain(self, email: str) -> Optional[str]:
        """Extract domain from email address for privacy"""
        if not email or '@' not in email:
            return None
        return email.split('@')[-1].lower()
    
    @cached(ttl=1800, key_prefix="gmail_labels")
    async def get_gmail_labels_cached(self, user) -> List[Dict[str, Any]]:
        """Get Gmail labels with caching"""
        try:
            # This would implement Gmail labels API call
            # Placeholder for actual implementation
            return []
        except Exception as e:
            logger.error(f"Failed to get Gmail labels: {e}")
            return []
    
    async def health_check_performance(self) -> Dict[str, Any]:
        """Performance-aware health check"""
        health_data = {
            "service": "HighPerformanceEmailService",
            "status": "healthy",
            "cache_status": "unknown",
            "performance_metrics": {}
        }
        
        try:
            # Test cache performance
            start_time = datetime.utcnow()
            test_key = f"health_check:{int(start_time.timestamp())}"
            
            await performance_cache.set(test_key, {"test": True}, ttl=60)
            cached_value = await performance_cache.get(test_key)
            await performance_cache.delete(test_key)
            
            cache_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if cached_value and cached_value.get("test"):
                health_data["cache_status"] = "healthy"
                health_data["performance_metrics"]["cache_roundtrip_ms"] = round(cache_time, 2)
            else:
                health_data["cache_status"] = "degraded"
            
        except Exception as e:
            health_data["cache_status"] = "error"
            health_data["cache_error"] = str(e)
        
        return health_data
    
    def get_supported_providers(self) -> List[str]:
        """Get list of supported email providers"""
        return ["gmail"]  # Currently only Gmail is supported
    
    async def get_provider_status(self, provider: str) -> Dict[str, Any]:
        """Get status of a specific email provider"""
        if provider.lower() != "gmail":
            return {
                "provider": provider,
                "status": "unsupported",
                "message": "Provider not supported"
            }
        
        try:
            # Check Gmail API accessibility
            health_data = await self.health_check_performance()
            
            return {
                "provider": "gmail",
                "status": "active" if health_data.get("status") == "healthy" else "degraded",
                "api_status": health_data.get("gmail_api_status", "unknown"),
                "oauth_status": "configured" if settings.GOOGLE_CLIENT_ID else "not_configured",
                "last_check": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to check Gmail provider status: {e}")
            return {
                "provider": "gmail",
                "status": "error",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }

# Service instantiation - create when needed
email_service = None

def get_email_service():
    """Get or create email service instance"""
    global email_service
    if email_service is None:
        email_service = HighPerformanceEmailService()
    return email_service

# Initialize service
email_service = get_email_service()
email_service = email_service

__all__ = [
    "HighPerformanceEmailService",
    "get_email_service", 
    "email_service",
    "email_service"
]
