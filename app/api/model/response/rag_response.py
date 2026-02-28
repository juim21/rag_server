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