from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.rag_controller import router as rag_router
from dotenv import load_dotenv

load_dotenv() 


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚀 애플리케이션 시작 시 실행
    print("애플리케이션 시작 - 의존성 주입 설정")
    setup_dependencies()
    yield
    # 🔒 애플리케이션 종료 시 실행  
    print("애플리케이션 종료 - 리소스 정리")
    cleanup_resources() 


app = FastAPI(title="RAG SQL API", version="1.0.0",lifespan=lifespan)


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
    from app.di_container import DIContainer

    DIContainer.register(RagRepository, AgeRepositoryImpl())
    DIContainer.register(LlmClient, GoogleChatClient())
    DIContainer.register(RerankClient, CrossEncoderClient())

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
## TODO : rag의 경우에는 이미지를 입력 받아서 기존 구축된 rag에 추가하는 기능 제공 피룡.
app.include_router(rag_router, prefix="/api/rag", tags=["RAG"])



