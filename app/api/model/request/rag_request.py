from pydantic import BaseModel
from typing import Optional, Dict, Any

class RAGRequest(BaseModel):
    collection_name: str

class RAGSearchRequest(BaseModel):
    collection_name: str
    query: str
    k: int = 5
    filters: Optional[Dict[str, Any]] = None  # 예: {"service_name": "my_service", "access_level": "user"}
    search_mode: str = "vector"  # "vector" | "hybrid" (벡터+BM25 RRF)

class RAGCodeAnalyzeRequest(BaseModel):
    collection_name: str
    code: str               # 분석할 소스코드
    k: int = 5              # 관련 화면 검색 수
    filters: Optional[Dict[str, Any]] = None  # 메타데이터 필터