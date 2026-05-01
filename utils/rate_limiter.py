# utils/rate_limiter.py
"""
Rate limiter for API calls
"""

import asyncio
import time
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(self, rate: float = 3.0, burst: int = 5):
        """
        Initialize rate limiter
        
        Args:
            rate: Sustained requests per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self._lock = None
        
    async def acquire(self, tokens: int = 1):
        """Acquire tokens before making a request"""
        # Create lock lazily in the correct event loop
        if self._lock is None:
            self._lock = asyncio.Lock()
            
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Add tokens based on time elapsed
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            
            # Wait if not enough tokens
            if tokens > self.tokens:
                wait_time = (tokens - self.tokens) / self.rate
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self.tokens = tokens
                
            self.tokens -= tokens


class ProviderRateLimiter:
    """Manage rate limiters for different providers"""
    
    def __init__(self, config: Dict[str, Any]):
        self.limiters = {}
        
        # OpenAI limits (adjust based on your tier)
        self.limiters['openai'] = {
            'gpt-3.5-turbo': RateLimiter(rate=3.0, burst=5),  # 3 req/sec sustained
            'gpt-4o-mini': RateLimiter(rate=2.0, burst=3),    # 2 req/sec sustained
            'gpt-4o': RateLimiter(rate=1.0, burst=2),         # 1 req/sec sustained
        }
        
        # Google limits (Gemma is quite generous)
        self.limiters['google'] = {
            'gemma-3-27b-it': RateLimiter(rate=10.0, burst=20),  # 10 req/sec
        }
        
        # Override with config if provided
        if 'rate_limits' in config:
            for provider, models in config['rate_limits'].items():
                if provider not in self.limiters:
                    self.limiters[provider] = {}
                for model, limits in models.items():
                    self.limiters[provider][model] = RateLimiter(
                        rate=limits.get('rate', 1.0),
                        burst=limits.get('burst', 2)
                    )
    
    async def acquire(self, provider: str, model: str):
        """Acquire permission to make a request"""
        if provider in self.limiters and model in self.limiters[provider]:
            await self.limiters[provider][model].acquire()
        else:
            # Default rate limit if not configured
            await asyncio.sleep(0.5)  # Simple fallback
