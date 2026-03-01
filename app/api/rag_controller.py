from app.core.service.rag_generation_service import RagGenerationService
from app.di_container import DIContainer
from app.api.model.response import RAGResponse, RAGSearchResponse
from app.api.model.response.rag_response import RAGCodeAnalyzeResponse
from app.api.model.request.rag_request import RAGRequest, RAGSearchRequest, RAGCodeAnalyzeRequest
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi import Form, UploadFile, File, Request
from typing import List


router = APIRouter()

@router.post("/generation/vector", response_model = RAGResponse)
def generate_rag(request: RAGRequest) -> JSONResponse:

    ragGenService = DIContainer.get(RagGenerationService)

    ragGenService.generation_rag(collection_name = request.collection_name)

    #응답 형식으로 변경
    return JSONResponse(content={
            "result" : "ok"
        })

## 멀티파트 형태로 벡터 추가데이터 넣기.
@router.post("/add/vector")
async def add_rag(request: Request) -> JSONResponse:
    
    ragGenService = DIContainer.get(RagGenerationService)
    
    formData = await request.form()
    
    
    temp = ragGenService.add_rag_data(
        collection_name = formData.get("collection_name")
        , formData = formData)
    
    return JSONResponse(content={
            "result" : "ok"
        })

## 멀티파트 형태로 텍스트 벡터 추가데이터 넣기.
@router.post("/add/text")
async def add_rag_text(request: Request) -> JSONResponse:

    ragGenService = DIContainer.get(RagGenerationService)

    formData = await request.form()

    ragGenService.add_rag_text_data(
        collection_name = formData.get("collection_name"),
        formData = formData
    )

    return JSONResponse(content={
            "result" : "ok"
        })

@router.post("/search", response_model=RAGSearchResponse)
def search_rag(request: RAGSearchRequest) -> JSONResponse:
    ragGenService = DIContainer.get(RagGenerationService)

    results = ragGenService.search_rag(
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
def analyze_code(request: RAGCodeAnalyzeRequest) -> JSONResponse:
    """
    소스코드를 분석하여 영향받는 화면을 탐지하고 테스트 영향도 리포트를 생성합니다.
    1단계: LLM으로 코드 기능 요약
    2단계: 요약 임베딩으로 관련 화면 RAG 검색
    3단계: LLM으로 영향도 분석 리포트 생성
    """
    ragGenService = DIContainer.get(RagGenerationService)

    result = ragGenService.analyze_code_impact(
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

@router.get("/health")
async def health_check():
    """서비스 상태 확인"""
    return {"status": "healthy", "service": "rag-generation"}
    
    


