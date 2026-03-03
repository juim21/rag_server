import os
import time
import structlog
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

logger = structlog.get_logger()

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# 환경변수에서 허용 키 목록 로드 (쉼표 구분, 미설정 시 인증 비활성화)
def _load_valid_keys() -> set[str]:
    raw = os.getenv("API_KEYS", "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}

# Rate Limit: 분당 최대 요청 수 (기본 60)
_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


async def verify_api_key(api_key: str = Security(_API_KEY_HEADER)):
    """
    X-API-Key 헤더 인증 FastAPI dependency.
    - API_KEYS 미설정 시 인증 비활성화 (개발 환경 편의)
    - 설정 시 헤더 누락 → 401, 잘못된 키 → 403
    """
    valid_keys = _load_valid_keys()

    if not valid_keys:
        # 인증 비활성화 모드 (개발용)
        return None

    if not api_key:
        logger.warning("api_auth_missing_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key 헤더가 필요합니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key not in valid_keys:
        logger.warning("api_auth_invalid_key", key_prefix=api_key[:6] + "...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효하지 않은 API Key입니다.",
        )

    return api_key


async def rate_limit(api_key: str = Security(_API_KEY_HEADER)):
    """
    Redis 기반 슬라이딩 윈도우 Rate Limiter (분당 RATE_LIMIT_PER_MINUTE 요청).
    Redis 미설정 시 rate limit 비활성화.
    """
    from app.di_container import DIContainer
    from app.core.interface.cache_client import CacheClient
    from app.infra.external.cache.redis_cache_client import NullCacheClient

    try:
        cache = DIContainer.get(CacheClient)
    except Exception:
        return  # DI 미초기화 시 pass

    if isinstance(cache, NullCacheClient):
        return  # Redis 없으면 rate limit 비적용

    identifier = api_key[:16] if api_key else "anonymous"
    window = int(time.time()) // 60  # 1분 단위 윈도우
    key = f"rl:{identifier}:{window}"

    try:
        import redis.asyncio as aioredis
        # RedisCacheClient 내부 _redis 접근
        r = cache._redis
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)

        if count > _RATE_LIMIT:
            logger.warning("rate_limit_exceeded", identifier=identifier, count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"요청 한도 초과: 분당 {_RATE_LIMIT}회까지 허용됩니다.",
                headers={"Retry-After": "60"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("rate_limit_error", error=str(e))
        # Rate limit 오류 시 요청 허용 (graceful degradation)
