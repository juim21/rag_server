import logging
from typing import Optional

from app.core.interface.cache_client import CacheClient

logger = logging.getLogger(__name__)


class RedisCacheClient(CacheClient):
    """Redis 비동기 캐시 클라이언트."""

    def __init__(self, host: str, port: int = 6379, db: int = 0, password: Optional[str] = None):
        import redis.asyncio as aioredis
        self._redis = aioredis.Redis(
            host=host,
            port=port,
            db=db,
            password=password or None,
            decode_responses=True,
        )

    async def get(self, key: str) -> Optional[str]:
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.warning(f"[Cache] GET 실패 key={key}: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 3600):
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception as e:
            logger.warning(f"[Cache] SET 실패 key={key}: {e}")

    async def delete_pattern(self, pattern: str):
        """SCAN으로 패턴 일치 키를 일괄 삭제 (KEYS 명령 회피)."""
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"[Cache] DELETE_PATTERN 실패 pattern={pattern}: {e}")

    async def close(self):
        await self._redis.aclose()


class NullCacheClient(CacheClient):
    """Redis 미설정 시 사용하는 no-op 캐시 클라이언트 (하위 호환)."""

    async def get(self, key: str) -> Optional[str]:
        return None

    async def set(self, key: str, value: str, ttl: int = 3600):
        pass

    async def delete_pattern(self, pattern: str):
        pass
