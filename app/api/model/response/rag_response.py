from pydantic import BaseModel
from typing import List, Dict, Any

class RAGResponse(BaseModel):
    message: str = "rag 생성 성공"

class SearchResultItem(BaseModel):
    content: str
    metadata: Dict[str, Any]
    score: float

class RAGSearchResponse(BaseModel):
    results: List[SearchResultItem]

class RAGCodeAnalyzeResponse(BaseModel):
    related_screens: List[SearchResultItem]  # 관련 화면 목록
    analysis: str                            # LLM 영향도 분석 리포트

class GraphScreenItem(BaseModel):
    screen_name: str
    content: str
    metadata: Dict[str, Any]

class GraphScreensResponse(BaseModel):
    screens: List[GraphScreenItem]
    total: int