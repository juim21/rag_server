from pydantic import BaseModel
from typing import Optional, Dict, Any

class RAGRequest(BaseModel):
    collection_name: str

class RAGSearchRequest(BaseModel):
    collection_name: str
    query: str
    k: int = 5
    filters: Optional[Dict[str, Any]] = None  # 예: {"service_name": "my_service", "access_level": "user"}