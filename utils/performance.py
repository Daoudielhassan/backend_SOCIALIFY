"""
Performance Optimization Layer - Comprehensive Performance Enhancements
Implements caching, async optimizations, and query batching
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union, Callable
from functools import wraps, lru_cache
from datetime import datetime, timedelta
from dataclasses import dataclass
import hashlib
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.orm import selectinload

from config.settings import settings
from utils.logger import logger

# Try to import Redis, fallback to in-memory cache if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using in-memory cache")

@dataclass
class CacheConfig:
    """Configuration for different cache types"""
    default_ttl: int = 300  # 5 minutes
    user_analytics_ttl: int = 600  # 10 minutes
    ai_predictions_ttl: int = 1800  # 30 minutes
    system_metrics_ttl: int = 60  # 1 minute
    message_counts_ttl: int = 120  # 2 minutes

class PerformanceCache:
    """
    High-performance caching layer with Redis fallback to in-memory
    
    Provides intelligent caching for database queries, AI predictions,
    and frequently accessed data with automatic invalidation.
    """
    
    def __init__(self):
        self.config = CacheConfig()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._redis_client: Optional[redis.Redis] = None
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Initialize Redis connection if available"""
        if not REDIS_AVAILABLE:
            return
        
        try:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            self._redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info("✅ Redis cache initialized")
        except Exception as e:
            logger.warning(f"Redis connection failed, using memory cache: {e}")
            self._redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache (Redis first, then memory)"""
        try:
            # Try Redis first
            if self._redis_client:
                value = await self._redis_client.get(key)
                if value:
                    return json.loads(value)
            
            # Fallback to memory cache
            if key in self._memory_cache:
                cache_entry = self._memory_cache[key]
                if cache_entry['expires'] > time.time():
                    return cache_entry['value']
                else:
                    del self._memory_cache[key]
            
            return None
            
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache with TTL"""
        try:
            ttl = ttl or self.config.default_ttl
            
            # Serialize value
            serialized_value = json.dumps(value, default=str)
            
            # Try Redis first
            if self._redis_client:
                await self._redis_client.setex(key, ttl, serialized_value)
            else:
                # Memory cache fallback
                self._memory_cache[key] = {
                    'value': value,
                    'expires': time.time() + ttl
                }
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if self._redis_client:
                await self._redis_client.delete(key)
            
            if key in self._memory_cache:
                del self._memory_cache[key]
            
            return True
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern"""
        try:
            deleted_count = 0
            
            if self._redis_client:
                keys = await self._redis_client.keys(pattern)
                if keys:
                    deleted_count = await self._redis_client.delete(*keys)
            
            # Memory cache pattern matching
            keys_to_delete = [k for k in self._memory_cache.keys() if pattern.replace('*', '') in k]
            for key in keys_to_delete:
                del self._memory_cache[key]
                deleted_count += 1
            
            logger.info(f"Invalidated {deleted_count} cache keys matching pattern: {pattern}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Cache pattern invalidation error for {pattern}: {e}")
            return 0
    
    def cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key"""
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        
        key_string = ":".join(key_parts)
        # Hash long keys to prevent Redis key length issues
        if len(key_string) > 200:
            key_hash = hashlib.md5(key_string.encode()).hexdigest()
            return f"{prefix}:hash:{key_hash}"
        
        return key_string

# Global cache instance
performance_cache = PerformanceCache()

def cached(ttl: int = None, key_prefix: str = "default"):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = performance_cache.cache_key(
                f"func:{key_prefix}:{func.__name__}",
                *args,
                **kwargs
            )
            
            # Try to get from cache
            cached_result = await performance_cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            cache_ttl = ttl or performance_cache.config.default_ttl
            await performance_cache.set(cache_key, result, cache_ttl)
            
            logger.debug(f"Cached result for {func.__name__}")
            return result
        
        return wrapper
    return decorator

class BatchProcessor:
    """
    Batch processing for database operations and API calls
    
    Reduces database round trips and improves performance for
    bulk operations like message processing and analytics.
    """
    
    @staticmethod
    async def batch_database_inserts(
        db: AsyncSession,
        model_class,
        records: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Batch insert records with optimal performance
        
        Args:
            db: Database session
            model_class: SQLAlchemy model class
            records: List of record dictionaries
            batch_size: Size of each batch
            
        Returns:
            Number of records inserted
        """
        if not records:
            return 0
        
        total_inserted = 0
        
        try:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                
                # Create model instances
                instances = [model_class(**record) for record in batch]
                
                # Bulk insert
                db.add_all(instances)
                await db.commit()
                
                total_inserted += len(batch)
                
                logger.debug(f"Batch inserted {len(batch)} {model_class.__name__} records")
            
            logger.info(f"Successfully batch inserted {total_inserted} {model_class.__name__} records")
            return total_inserted
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Batch insert failed: {e}")
            raise
    
    @staticmethod
    async def batch_update_records(
        db: AsyncSession,
        model_class,
        updates: List[Dict[str, Any]],
        key_field: str = "id",
        batch_size: int = 100
    ) -> int:
        """
        Batch update records efficiently
        
        Args:
            db: Database session
            model_class: SQLAlchemy model class
            updates: List of update dictionaries (must include key_field)
            key_field: Field to use for matching records
            batch_size: Size of each batch
            
        Returns:
            Number of records updated
        """
        if not updates:
            return 0
        
        total_updated = 0
        
        try:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                
                for update_data in batch:
                    key_value = update_data.pop(key_field)
                    
                    # Build update query
                    stmt = (
                        model_class.__table__.update()
                        .where(getattr(model_class, key_field) == key_value)
                        .values(**update_data)
                    )
                    
                    await db.execute(stmt)
                
                await db.commit()
                total_updated += len(batch)
                
                logger.debug(f"Batch updated {len(batch)} {model_class.__name__} records")
            
            logger.info(f"Successfully batch updated {total_updated} {model_class.__name__} records")
            return total_updated
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Batch update failed: {e}")
            raise
    
    @staticmethod
    async def parallel_api_calls(
        api_calls: List[Callable],
        max_concurrent: int = 5,
        timeout: float = 30.0
    ) -> List[Any]:
        """
        Execute API calls in parallel with concurrency control
        
        Args:
            api_calls: List of async callable functions
            max_concurrent: Maximum concurrent requests
            timeout: Timeout for each call
            
        Returns:
            List of results (None for failed calls)
        """
        if not api_calls:
            return []
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def bounded_call(call):
            async with semaphore:
                try:
                    return await asyncio.wait_for(call(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"API call timed out after {timeout}s")
                    return None
                except Exception as e:
                    logger.error(f"API call failed: {e}")
                    return None
        
        # Execute all calls concurrently
        results = await asyncio.gather(
            *[bounded_call(call) for call in api_calls],
            return_exceptions=True
        )
        
        # Count successful calls
        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logger.info(f"Parallel API calls: {successful}/{len(api_calls)} successful")
        
        return results

class QueryOptimizer:
    """
    Database query optimization utilities
    
    Provides optimized query patterns, eager loading strategies,
    and performance monitoring for database operations.
    """
    
    @staticmethod
    async def get_user_messages_optimized(
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        source: Optional[str] = None,
        days: int = 30
    ) -> List[Any]:
        """
        Optimized user messages query with proper indexing
        """
        from db.models import MessageMetadata
        
        # Build query with optimal index usage
        conditions = [MessageMetadata.user_id == user_id]
        
        # Date filter using index
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)
            conditions.append(MessageMetadata.received_at >= start_date)
        
        # Source filter using composite index
        if source:
            conditions.append(MessageMetadata.source == source)
        
        # Optimized query using composite index
        query = (
            select(MessageMetadata)
            .where(and_(*conditions))
            .order_by(MessageMetadata.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_analytics_data_batch(
        db: AsyncSession,
        user_ids: List[int],
        days: int = 30
    ) -> Dict[int, Dict[str, Any]]:
        """
        Batch analytics data retrieval for multiple users
        """
        from db.models import MessageMetadata
        
        if not user_ids:
            return {}
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Single query for all users using optimized indexes
        query = (
            select(
                MessageMetadata.user_id,
                MessageMetadata.source,
                MessageMetadata.predicted_priority,
                func.count(MessageMetadata.id).label('count')
            )
            .where(
                and_(
                    MessageMetadata.user_id.in_(user_ids),
                    MessageMetadata.received_at >= start_date
                )
            )
            .group_by(
                MessageMetadata.user_id,
                MessageMetadata.source,
                MessageMetadata.predicted_priority
            )
        )
        
        result = await db.execute(query)
        rows = result.fetchall()
        
        # Organize results by user
        analytics_data = {user_id: {"sources": {}, "priorities": {}} for user_id in user_ids}
        
        for row in rows:
            user_data = analytics_data[row.user_id]
            user_data["sources"][row.source] = user_data["sources"].get(row.source, 0) + row.count
            user_data["priorities"][row.predicted_priority] = user_data["priorities"].get(row.predicted_priority, 0) + row.count
        
        return analytics_data
    
    @staticmethod
    async def execute_with_performance_monitoring(
        db: AsyncSession,
        query,
        query_name: str = "unknown",
        parameters: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute query with performance monitoring
        """
        start_time = time.time()
        
        try:
            if parameters:
                result = await db.execute(query, parameters)
            else:
                result = await db.execute(query)
            execution_time = time.time() - start_time
            
            if execution_time > 1.0:  # Log slow queries
                logger.warning(f"Slow query '{query_name}': {execution_time:.2f}s")
            else:
                logger.debug(f"Query '{query_name}': {execution_time:.3f}s")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Query '{query_name}' failed after {execution_time:.3f}s: {e}")
            raise

# Global instances
batch_processor = BatchProcessor()
query_optimizer = QueryOptimizer()

# Performance monitoring decorators
def monitor_performance(operation_name: str):
    """Decorator to monitor operation performance"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.info(f"Performance: {operation_name} completed in {execution_time:.3f}s")
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"Performance: {operation_name} failed after {execution_time:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator

# Export all performance utilities
__all__ = [
    "performance_cache",
    "cached",
    "batch_processor", 
    "query_optimizer",
    "monitor_performance",
    "CacheConfig",
    "PerformanceCache",
    "BatchProcessor", 
    "QueryOptimizer"
]
