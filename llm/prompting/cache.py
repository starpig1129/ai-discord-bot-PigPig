import threading
from addons.logging import get_logger
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
from function import func
import asyncio

class PromptCache:
    """Intelligent caching system for prompt components and combinations."""
    
    def __init__(self):
        """Initialize the cache storage and monitoring structures."""
        self.cache_storage: Dict[str, Any] = {}
        self.ttl_storage: Dict[str, datetime] = {}
        self.precompiled_cache: Dict[str, str] = {}
        self.access_count: Dict[str, int] = {}
        self._lock = threading.RLock()
        self.logger = get_logger(server_id="Bot", source="llm.prompting.cache")
        
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached item if it exists and has not expired.
        
        Args:
            key: The unique identifier for the cached item.
            
        Returns:
            The cached value if available and valid, otherwise None.
        """
        with self._lock:
            if key not in self.cache_storage:
                return None
            
            if self.is_expired(key):
                self.invalidate(key)
                return None
            
            # Record access frequency
            self.access_count[key] = self.access_count.get(key, 0) + 1
            
            return self.cache_storage[key]
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """
        Set a value in the cache with a specific time-to-live.
        
        Args:
            key: The unique identifier for the cached item.
            value: The data to be cached.
            ttl: Time-to-live in seconds (default is 3600).
        """
        with self._lock:
            self.cache_storage[key] = value
            self.ttl_storage[key] = datetime.now() + timedelta(seconds=ttl)
            self.access_count[key] = 0
            
            self.logger.debug(f"Cached item: {key} (TTL: {ttl}s)")
    
    def invalidate(self, key: str) -> None:
        """
        Explicitly remove an item from the cache.
        
        Args:
            key: The unique identifier of the item to invalidate.
        """
        with self._lock:
            self.cache_storage.pop(key, None)
            self.ttl_storage.pop(key, None)
            self.access_count.pop(key, None)
            self.precompiled_cache.pop(key, None)
            
            self.logger.debug(f"Invalidated cache item: {key}")
    
    def clear_all(self) -> None:
        """Clear all cached items and metadata."""
        with self._lock:
            cleared_count = len(self.cache_storage)
            self.cache_storage.clear()
            self.ttl_storage.clear()
            self.precompiled_cache.clear()
            self.access_count.clear()
            
            self.logger.info(f"Cleared all cache ({cleared_count} items)")
    
    def is_expired(self, key: str) -> bool:
        """
        Check if a cached item has passed its expiration time.
        
        Args:
            key: The cache key to check.
            
        Returns:
            True if the item is expired or does not exist, False otherwise.
        """
        if key not in self.ttl_storage:
            return True
        return datetime.now() > self.ttl_storage[key]
    
    def precompile_templates(self, config: dict) -> None:
        """
        Precompile common prompt module combinations to reduce runtime overhead.
        
        Args:
            config: The prompting configuration dictionary.
        """
        with self._lock:
            self.precompiled_cache.clear()
            
            try:
                # Precompile standard combinations
                default_modules = config.get('composition', {}).get('default_modules', [])
                module_order = config.get('composition', {}).get('module_order', default_modules)
                
                # Precompile combinations of different lengths
                for i in range(1, len(default_modules) + 1):
                    module_combo = [mod for mod in module_order if mod in default_modules[:i]]
                    combo_key = '_'.join(module_combo)
                    
                    # Store the combination key (actual construction handled by PromptBuilder)
                    self.precompiled_cache[f"combo_{combo_key}"] = combo_key
                
                # Precompile individual modules
                for module in default_modules:
                    if module in config:
                        self.precompiled_cache[f"module_{module}"] = module
                
                self.logger.info(f"Precompiled {len(self.precompiled_cache)} template combinations")
                
            except Exception as e:
                asyncio.create_task(func.report_error(e, "precompiling templates"))
    
    def get_precompiled(self, key: str) -> Optional[str]:
        """
        Retrieve a precompiled template combination.
        
        Args:
            key: The key of the precompiled template.
            
        Returns:
            The combination key if found, otherwise None.
        """
        return self.precompiled_cache.get(key)
    
    def cleanup_expired(self) -> int:
        """
        Iterate through the cache and remove all expired items.
        
        Returns:
            The number of items successfully removed.
        """
        with self._lock:
            expired_keys = []
            
            for key in list(self.cache_storage.keys()):
                if self.is_expired(key):
                    expired_keys.append(key)
            
            for key in expired_keys:
                self.invalidate(key)
            
            if expired_keys:
                self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
            
            return len(expired_keys)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retrieve usage and performance statistics for the cache.
        
        Returns:
            A dictionary containing cache performance metrics.
        """
        with self._lock:
            total_items = len(self.cache_storage)
            expired_items = sum(1 for key in self.cache_storage.keys() if self.is_expired(key))
            precompiled_items = len(self.precompiled_cache)
            
            # Calculate total access count
            total_access = sum(self.access_count.values())
            
            # Identify the most frequently accessed item
            most_accessed = None
            if self.access_count:
                most_accessed = max(self.access_count.items(), key=lambda x: x[1])
            
            return {
                'total_items': total_items,
                'expired_items': expired_items,
                'active_items': total_items - expired_items,
                'precompiled_items': precompiled_items,
                'total_access_count': total_access,
                'most_accessed': most_accessed
            }
    
    def get_cache_keys(self, prefix: str = '') -> Set[str]:
        """
        Retrieve all keys currently in the cache.
        
        Args:
            prefix: Optional filter to only return keys starting with this string.
            
        Returns:
            A set of matching cache keys.
        """
        with self._lock:
            if prefix:
                return {key for key in self.cache_storage.keys() if key.startswith(prefix)}
            return set(self.cache_storage.keys())
    
    def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        Extend the life of a cached item by adding more time to its expiration.
        
        Args:
            key: The unique identifier for the cached item.
            additional_seconds: Seconds to add to the existing TTL.
            
        Returns:
            True if the TTL was successfully extended, False otherwise.
        """
        with self._lock:
            if key in self.ttl_storage and not self.is_expired(key):
                self.ttl_storage[key] += timedelta(seconds=additional_seconds)
                self.logger.debug(f"Extended TTL for {key} by {additional_seconds} seconds")
                return True
            return False