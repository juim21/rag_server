from pydantic import BaseModel

class RAGRequest(BaseModel):
    collection_name: str

class RAGSearchRequest(BaseModel):
    collection_name: str
    query: str
    k: int = 5