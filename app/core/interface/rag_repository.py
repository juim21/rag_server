from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional

class RagRepository(ABC):

    @abstractmethod
    def save_documents(self, collection_name: str, documents: List[Dict[str, Any]]):
        """문서와 메타데이터를 그래프에 저장합니다."""
        pass

    @abstractmethod
    def similarity_search(self, collection_name: str, query_embedding: List[float], k: int = 5,
                          filters: Optional[Dict[str, Any]] = None,
                          search_mode: str = "vector", query_text: Optional[str] = None) -> List[Tuple[Dict[str, Any], float]]:
        """임베딩과 유사한 문서를 검색합니다.
        filters: 메타데이터 필드 조건
        search_mode: 'vector'(기본) | 'hybrid'(벡터+BM25 RRF)
        query_text: hybrid 모드에서 BM25 키워드 검색에 사용할 원본 쿼리
        """
        pass

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """컬렉션(그래프)의 존재 여부를 확인합니다."""
        pass

    @abstractmethod
    def get_screens_by_service(self, service_name: str, version: Optional[str] = None) -> List[Dict[str, Any]]:
        """서비스에 속한 화면 노드 전체를 AGE 그래프에서 조회합니다."""
        pass

    @abstractmethod
    def get_related_screens(self, collection_name: str, screen_name: str) -> List[Dict[str, Any]]:
        """같은 서비스에 속한 연관 화면 노드를 AGE 그래프에서 조회합니다."""
        pass
