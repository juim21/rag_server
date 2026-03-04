from pydantic import BaseModel
from typing import Optional, Dict, Any

class RAGRequest(BaseModel):
    collection_name: str
    system_id: Optional[str] = None  # 시스템 구분자 (예: "system01")

class RAGSearchRequest(BaseModel):
    collection_name: str
    query: str
    k: int = 5
    filters: Optional[Dict[str, Any]] = None  # 예: {"service_name": "my_service", "access_level": "user"}
    search_mode: str = "vector"  # "vector" | "hybrid" (벡터+BM25 RRF)
    rerank: bool = False  # True: 크로스인코더 재랭킹 적용 (k*3 오버패치 후 재정렬)
    system_id: Optional[str] = None  # 시스템 구분자 (예: "system01")

class RAGCodeAnalyzeRequest(BaseModel):
    collection_name: str
    code: str               # 분석할 소스코드
    k: int = 5              # 관련 화면 검색 수
    filters: Optional[Dict[str, Any]] = None  # 메타데이터 필터
    system_id: Optional[str] = None  # 시스템 구분자 (예: "system01")