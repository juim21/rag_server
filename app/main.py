import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.rag_controller import router as rag_router
from dotenv import load_dotenv

load_dotenv()

import structlog

# 모듈 로드 시점에 즉시 설정 (lifespan 이전, 모든 import 완료 후)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_start", message="의존성 주입 설정")
    setup_dependencies()
    yield
    logger.info("application_stop", message="리소스 정리")
    cleanup_resources()


app = FastAPI(title="RAG SQL API", version="1.0.0", lifespan=lifespan)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


def setup_dependencies():
    import os
    from app.infra.repository.age_repository_impl import AgeRepositoryImpl
    from app.core.service.rag_generation_service import RagGenerationService
    from app.core.interface import RagRepository
    from app.core.interface.llm_client import LlmClient
    from app.core.interface.rerank_client import RerankClient
    from app.core.interface.cache_client import CacheClient
    from app.infra.external.llm.google_client import GoogleChatClient
    from app.infra.external.rerank.cross_encoder_client import CrossEncoderClient
    from app.infra.external.cache.redis_cache_client import RedisCacheClient, NullCacheClient
    from app.core.interface.multimodal_embedding_client import MultimodalEmbeddingClient
    from app.infra.external.embedding.clip_embedding_client import ClipEmbeddingClient
    from app.di_container import DIContainer

    DIContainer.register(RagRepository, AgeRepositoryImpl())
    DIContainer.register(LlmClient, GoogleChatClient())
    DIContainer.register(RerankClient, CrossEncoderClient())
    DIContainer.register(MultimodalEmbeddingClient, ClipEmbeddingClient())

    redis_host = os.getenv("REDIS_HOST")
    if redis_host:
        DIContainer.register(CacheClient, RedisCacheClient(
            host=redis_host,
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
        ))
    else:
        DIContainer.register(CacheClient, NullCacheClient())

    DIContainer.register(RagGenerationService, RagGenerationService())


def cleanup_resources():
    ## TODO : 디비 정리등 리소스 정리를 만들어야 함.
    pass


# 라우터 등록
app.include_router(rag_router, prefix="/api/rag", tags=["RAG"])
