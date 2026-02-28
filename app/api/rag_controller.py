from app.core.service.rag_generation_service import RagGenerationService
from app.di_container import DIContainer
from app.api.model.response import RAGResponse, RAGSearchResponse
from app.api.model.request.rag_request import RAGRequest, RAGSearchRequest
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
        k=request.k
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

@router.get("/health")
async def health_check():
    """서비스 상태 확인"""
    return {"status": "healthy", "service": "rag-generation"}
    
    


