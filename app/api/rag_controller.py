from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Optional

from app.core.service.rag_generation_service import RagGenerationService
from app.di_container import DIContainer
from app.api.model.response import RAGResponse, RAGSearchResponse
from app.api.model.response.rag_response import RAGCodeAnalyzeResponse, GraphScreensResponse
from app.api.model.request.rag_request import RAGRequest, RAGSearchRequest, RAGCodeAnalyzeRequest


router = APIRouter()


@router.post("/generation/vector", response_model=RAGResponse)
async def generate_rag(request: RAGRequest) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    await ragGenService.generation_rag(collection_name=request.collection_name)
    return JSONResponse(content={"result": "ok"})


@router.post("/add/vector")
async def add_rag(request: Request) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    formData = await request.form()
    await ragGenService.add_rag_data(
        collection_name=formData.get("collection_name"),
        formData=formData
    )
    return JSONResponse(content={"result": "ok"})


@router.post("/add/text")
async def add_rag_text(request: Request) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    formData = await request.form()
    await ragGenService.add_rag_text_data(
        collection_name=formData.get("collection_name"),
        formData=formData
    )
    return JSONResponse(content={"result": "ok"})


@router.post("/search", response_model=RAGSearchResponse)
async def search_rag(request: RAGSearchRequest) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)
    results = await ragGenService.search_rag(
        collection_name=request.collection_name,
        query=request.query,
        k=request.k,
        filters=request.filters,
        search_mode=request.search_mode
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


@router.post("/analyze/code", response_model=RAGCodeAnalyzeResponse)
async def analyze_code(request: RAGCodeAnalyzeRequest) -> JSONResponse:
    """
    소스코드를 분석하여 영향받는 화면을 탐지하고 테스트 영향도 리포트를 생성합니다.
    1단계: LLM으로 코드 기능 요약
    2단계: 요약 임베딩으로 관련 화면 RAG 검색
    3단계: LLM으로 영향도 분석 리포트 생성
    """
    ragGenService = DIContainer.get(RagGenerationService)
    result = await ragGenService.analyze_code_impact(
        collection_name=request.collection_name,
        code=request.code,
        k=request.k,
        filters=request.filters
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


@router.get("/graph/service/{service_name}", response_model=GraphScreensResponse)
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


@router.get("/graph/screen/{collection_name}/{screen_name}/related", response_model=GraphScreensResponse)
async def get_related_screens(collection_name: str, screen_name: str) -> JSONResponse:
    """
    AGE 그래프에서 같은 서비스에 속한 연관 화면을 조회합니다.
    - collection_name: 컬렉션(노드 레이블)명
    - screen_name: 기준 화면명
    """
    ragGenService = DIContainer.get(RagGenerationService)
    screens = await ragGenService.get_related_screens(collection_name, screen_name)
    return JSONResponse(content={
        "screens": screens,
        "total": len(screens)
    })


@router.get("/health")
async def health_check():
    """서비스 상태 확인"""
    return {"status": "healthy", "service": "rag-generation"}
