import asyncio
import base64
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from typing import Optional

from app.core.service.rag_generation_service import RagGenerationService
from app.di_container import DIContainer
from app.api.model.response import RAGResponse, RAGSearchResponse
from app.api.model.response.rag_response import RAGCodeAnalyzeResponse, GraphScreensResponse
from app.api.model.request.rag_request import RAGRequest, RAGSearchRequest, RAGCodeAnalyzeRequest
from app.core.middleware.security import verify_api_key, rate_limit

router = APIRouter()

# 인증 + Rate Limit을 묶은 공통 dependency
_secured = [Depends(verify_api_key), Depends(rate_limit)]


def _prefixed_collection(request: Request, collection_name: str) -> str:
    """
    request.state.tenant 기반으로 collection_name에 자동 prefix를 붙입니다.
    tenant가 없거나 'default'이면 원본 collection_name 그대로 반환.
    예) tenant='system01', collection_name='screens' → 'system01:screens'
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant != "default":
        return f"{tenant}:{collection_name}"
    return collection_name


@router.post("/generation/vector", response_model=RAGResponse, dependencies=_secured)
async def generate_rag(request: Request, body: RAGRequest) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    await ragGenService.generation_rag(
        collection_name=_prefixed_collection(request, body.collection_name)
    )
    return JSONResponse(content={"result": "ok"})


@router.post("/add/vector", dependencies=_secured)
async def add_rag(request: Request) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    formData = await request.form()
    await ragGenService.add_rag_data(
        collection_name=_prefixed_collection(request, formData.get("collection_name")),
        formData=formData
    )
    return JSONResponse(content={"result": "ok"})


@router.post("/add/text", dependencies=_secured)
async def add_rag_text(request: Request) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    formData = await request.form()
    await ragGenService.add_rag_text_data(
        collection_name=_prefixed_collection(request, formData.get("collection_name")),
        formData=formData
    )
    return JSONResponse(content={"result": "ok"})


@router.post("/search", response_model=RAGSearchResponse, dependencies=_secured)
async def search_rag(request: Request, body: RAGSearchRequest) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    results = await ragGenService.search_rag(
        collection_name=_prefixed_collection(request, body.collection_name),
        query=body.query,
        k=body.k,
        filters=body.filters,
        search_mode=body.search_mode,
        rerank=body.rerank
    )
    return JSONResponse(content={
        "results": [
            {
                "content": doc["page_content"],
                "metadata": doc["metadata"],
                "score": round(score, 4)
            }
            for doc, score in results
        ]
    })


@router.post("/search/image", dependencies=_secured)
async def search_by_image(request: Request) -> JSONResponse:
    """이미지 파일을 업로드하면 CLIP 임베딩으로 시각적으로 유사한 문서를 검색합니다."""
    ragGenService = DIContainer.get(RagGenerationService)
    formData = await request.form()
    collection_name = _prefixed_collection(request, formData.get("collection_name"))
    k = int(formData.get("k", 5))
    image_file = formData.get("image")
    base64_image = base64.b64encode(image_file.file.read()).decode("utf-8")

    results = await ragGenService.search_by_image(collection_name, base64_image, k)
    return JSONResponse(content={
        "results": [
            {
                "content": doc["page_content"],
                "metadata": doc["metadata"],
                "score": round(score, 4)
            }
            for doc, score in results
        ]
    })


@router.post("/analyze/code", response_model=RAGCodeAnalyzeResponse, dependencies=_secured)
async def analyze_code(request: Request, body: RAGCodeAnalyzeRequest) -> JSONResponse:
    """
    소스코드를 분석하여 영향받는 화면을 탐지하고 테스트 영향도 리포트를 생성합니다.
    1단계: LLM으로 코드 기능 요약
    2단계: 요약 임베딩으로 관련 화면 RAG 검색
    3단계: LLM으로 영향도 분석 리포트 생성
    """
    ragGenService = DIContainer.get(RagGenerationService)
    result = await ragGenService.analyze_code_impact(
        collection_name=_prefixed_collection(request, body.collection_name),
        code=body.code,
        k=body.k,
        filters=body.filters
    )
    return JSONResponse(content={
        "related_screens": [
            {
                "content": doc["page_content"],
                "metadata": doc["metadata"],
                "score": round(score, 4)
            }
            for doc, score in result["related_screens"]
        ],
        "analysis": result["analysis"]
    })


@router.get("/graph/service/{service_name}", response_model=GraphScreensResponse, dependencies=_secured)
async def get_screens_by_service(service_name: str, version: Optional[str] = None) -> JSONResponse:
    """
    AGE 그래프에서 서비스에 속한 화면 전체를 조회합니다.
    - service_name: 서비스 이름 (URL 인코딩 필요)
    - version: (선택) 특정 버전 필터
    """
    ragGenService = DIContainer.get(RagGenerationService)
    screens = await ragGenService.get_screens_by_service(service_name, version)
    return JSONResponse(content={
        "screens": screens,
        "total": len(screens)
    })


@router.get("/graph/screen/{collection_name}/{screen_name}/related", response_model=GraphScreensResponse, dependencies=_secured)
async def get_related_screens(request: Request, collection_name: str, screen_name: str) -> JSONResponse:
    """
    AGE 그래프에서 같은 서비스에 속한 연관 화면을 조회합니다.
    - collection_name: 컬렉션(노드 레이블)명
    - screen_name: 기준 화면명
    """
    ragGenService = DIContainer.get(RagGenerationService)
    screens = await ragGenService.get_related_screens(
        _prefixed_collection(request, collection_name),
        screen_name
    )
    return JSONResponse(content={
        "screens": screens,
        "total": len(screens)
    })


@router.get("/health")
async def health_check():
    """서비스 상태 확인 - DB 및 Redis 실제 연결 상태 반환 (인증 불필요)"""
    from app.core.interface import RagRepository
    from app.core.interface.cache_client import CacheClient

    checks = {"status": "ok", "db": "ok", "redis": "ok"}

    try:
        repo = DIContainer.get(RagRepository)
        await asyncio.to_thread(repo.health_check)
    except Exception as e:
        checks["db"] = f"error: {str(e)[:80]}"
        checks["status"] = "degraded"

    try:
        cache = DIContainer.get(CacheClient)
        await cache.ping()
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:80]}"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    return JSONResponse(content=checks, status_code=status_code)
