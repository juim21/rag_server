from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

class RagRepository(ABC):
    
    @abstractmethod
    def save_documents(self, collection_name: str, documents: List[Dict[str, Any]]):
        """문서와 메타데이터를 그래프에 저장합니다."""
        pass
    
    @abstractmethod
    def similarity_search(self, collection_name: str, query_embedding: List[float], k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """임베딩과 유사한 문서를 검색합니다."""
        pass
    
    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """컬렉션(그래프)의 존재 여부를 확인합니다."""
        pass
