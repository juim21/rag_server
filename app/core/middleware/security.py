import os
import time
import structlog
from fastapi import Request, Security, HTTPException, status
from fastapi.security import APIKeyHeader

logger = structlog.get_logger()

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Rate Limit: 분당 최대 요청 수 (기본 100)
_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))


def _load_key_tenant_map() -> dict[str, str]:
    """
    환경변수 API_KEYS에서 {api_key: tenant} 매핑을 로드합니다.
    형식: "tenant01:key1,tenant02:key2,..."
    tenant 없이 키만 있으면 "default" tenant로 처리.
    미설정 시 빈 dict → 인증 비활성화.
    """
    raw = os.getenv("API_KEYS", "").strip()
    if not raw:
        return {}
    result = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            tenant, key = item.split(":", 1)
            result[key.strip()] = tenant.strip()
        else:
            result[item] = "default"
    return result


async def verify_api_key(request: Request, api_key: str = Security(_API_KEY_HEADER)):
    """
    X-API-Key 헤더 인증 FastAPI dependency.
    - API_KEYS 미설정 시 인증 비활성화 (개발 환경 편의)
    - 인증 성공 시 request.state.tenant 에 tenant 이름 주입
    - 헤더 누락 → 401, 잘못된 키 → 403
    """
    key_tenant_map = _load_key_tenant_map()

    if not key_tenant_map:
        # 인증 비활성화 모드 (개발용) - tenant 없음
        request.state.tenant = None
        return None

    if not api_key:
        logger.warning("api_auth_missing_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key 헤더가 필요합니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key not in key_tenant_map:
        logger.warning("api_auth_invalid_key", key_prefix=api_key[:6] + "...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효하지 않은 API Key입니다.",
        )

    tenant = key_tenant_map[api_key]
    request.state.tenant = tenant
    logger.info("api_auth_ok", tenant=tenant)
    return api_key


async def rate_limit(request: Request, api_key: str = Security(_API_KEY_HEADER)):
    """
    Redis 기반 슬라이딩 윈도우 Rate Limiter (분당 RATE_LIMIT_PER_MINUTE 요청).
    tenant 단위로 Rate Limit 적용. Redis 미설정 시 비활성화.
    """
    from app.di_container import DIContainer
    from app.core.interface.cache_client import CacheClient
    from app.infra.external.cache.redis_cache_client import NullCacheClient

    try:
        cache = DIContainer.get(CacheClient)
    except Exception:
        return

    if isinstance(cache, NullCacheClient):
        return

    # tenant 기준 Rate Limit (tenant 없으면 api_key prefix 사용)
    tenant = getattr(request.state, "tenant", None)
    identifier = tenant if tenant else (api_key[:16] if api_key else "anonymous")
    window = int(time.time()) // 60
    key = f"rl:{identifier}:{window}"

    try:
        r = cache._redis
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)

        if count > _RATE_LIMIT:
            logger.warning("rate_limit_exceeded", tenant=identifier, count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"요청 한도 초과: 분당 {_RATE_LIMIT}회까지 허용됩니다.",
                headers={"Retry-After": "60"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("rate_limit_error", error=str(e))
